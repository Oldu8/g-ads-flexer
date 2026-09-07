"""Generate a local markdown snapshot of an account's *active* campaigns.

Usage:
    uv run scripts/snapshot.py [customer_id]

Defaults to the boo.ua account (5690318342) if no customer_id is given.
Writes to snapshots/<account-name-slug>.md, overwriting any previous
snapshot for that account. Re-run any time you want a refreshed audit
instead of querying the live API each time.

Scope: only ENABLED campaigns are included (paused/removed legacy campaigns
are dropped entirely - re-run scripts/gaql.py directly if you need those).
For each active campaign:
  - Search/Display-style campaigns: ad groups -> keywords + ads nested under
    each ad group.
  - Performance Max campaigns (no ad groups/keywords by design): asset
    groups, each with its audience signals (audience/search theme targeting
    inputs) and assets (headlines, descriptions, images, video) nested under it.
  - Extensions (campaign-level assets: sitelinks, callouts, structured
    snippets, calls, ...) shown per campaign regardless of type.
Not covered yet: ad-group-level assets (non-PMax), price/promotion extension
details beyond a label, raw image/video bytes. See TRACKER.md.
"""

import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sdk_client import GoogleAdsSdkClient  # noqa: E402
from src.utils import load_dotenv  # noqa: E402

DEFAULT_CUSTOMER_ID = "5690318342"  # boo.ua
SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "snapshots"


def micros(v: int) -> float:
    return (v or 0) / 1_000_000


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "account"


def asset_label(asset) -> str:
    """Best-effort human-readable label for an Asset, based on its type."""
    t = asset.type_.name
    if t == "SITELINK":
        return f'Sitelink: "{asset.sitelink_asset.link_text}"'
    if t == "CALLOUT":
        return f'Callout: "{asset.callout_asset.callout_text}"'
    if t == "STRUCTURED_SNIPPET":
        values = ", ".join(asset.structured_snippet_asset.values)
        return f"Snippet [{asset.structured_snippet_asset.header}]: {values}"
    if t == "CALL":
        return f"Call: {asset.call_asset.country_code} {asset.call_asset.phone_number}"
    if t == "PROMOTION":
        return f"Promotion: {asset.name or asset.resource_name}"
    if t == "PRICE":
        return f"Price: {asset.name or asset.resource_name}"
    if t == "TEXT":
        return f'Text: "{asset.text_asset.text or asset.name}"'
    return f"{t}: {asset.name or asset.resource_name}"


def main() -> None:
    customer_id = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CUSTOMER_ID).replace(
        "-", ""
    )

    load_dotenv()
    sdk = GoogleAdsSdkClient()
    ga_service = sdk.client.get_service("GoogleAdsService", version="v25")

    def search(query: str):
        return list(ga_service.search(customer_id=customer_id, query=query))

    # --- Account info ---
    account = search(
        """
        SELECT customer.id, customer.descriptive_name, customer.currency_code,
               customer.time_zone, customer.status
        FROM customer
        LIMIT 1
        """
    )[0].customer

    totals_rows = search(
        """
        SELECT metrics.cost_micros, metrics.clicks, metrics.impressions,
               metrics.conversions
        FROM customer
        WHERE segments.date DURING THIS_MONTH
        """
    )
    totals = totals_rows[0].metrics if totals_rows else None

    # --- Active campaigns only ---
    campaign_rows = search(
        """
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type,
               campaign.advertising_channel_sub_type,
               campaign.bidding_strategy_type,
               campaign.start_date_time, campaign.end_date_time,
               campaign_budget.id, campaign_budget.name,
               campaign_budget.amount_micros, campaign_budget.delivery_method,
               metrics.cost_micros, metrics.clicks, metrics.impressions,
               metrics.conversions
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY metrics.cost_micros DESC
        """
    )

    # --- Ad groups (Search/Display style campaigns) ---
    ad_group_rows = search(
        """
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.type,
               ad_group.campaign,
               metrics.cost_micros, metrics.clicks, metrics.impressions
        FROM ad_group
        WHERE ad_group.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY ad_group.id
        """
    )
    ad_groups_by_campaign: dict[str, list] = defaultdict(list)
    for row in ad_group_rows:
        ad_groups_by_campaign[row.ad_group.campaign].append(row)

    # --- Keywords ---
    keyword_rows = search(
        """
        SELECT ad_group_criterion.criterion_id, ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type, ad_group_criterion.status,
               ad_group_criterion.ad_group,
               metrics.clicks, metrics.impressions, metrics.cost_micros
        FROM keyword_view
        WHERE ad_group_criterion.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY metrics.clicks DESC
        """
    )
    keywords_by_ad_group: dict[str, list] = defaultdict(list)
    for row in keyword_rows:
        keywords_by_ad_group[row.ad_group_criterion.ad_group].append(row)

    # --- Ads ---
    ad_rows = search(
        """
        SELECT ad_group_ad.ad.id, ad_group_ad.ad.type, ad_group_ad.status,
               ad_group_ad.ad_group,
               ad_group_ad.ad.responsive_search_ad.headlines,
               ad_group_ad.ad.responsive_search_ad.descriptions,
               ad_group_ad.policy_summary.approval_status,
               metrics.clicks, metrics.impressions, metrics.cost_micros
        FROM ad_group_ad
        WHERE ad_group_ad.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY metrics.clicks DESC
        """
    )
    ads_by_ad_group: dict[str, list] = defaultdict(list)
    for row in ad_rows:
        ads_by_ad_group[row.ad_group_ad.ad_group].append(row)

    # --- Performance Max asset groups (campaigns with no ad groups) ---
    asset_group_rows = search(
        """
        SELECT asset_group.id, asset_group.name, asset_group.status,
               asset_group.campaign, asset_group.ad_strength,
               metrics.cost_micros, metrics.clicks, metrics.conversions
        FROM asset_group
        WHERE asset_group.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY asset_group.id
        """
    )
    asset_groups_by_campaign: dict[str, list] = defaultdict(list)
    for row in asset_group_rows:
        asset_groups_by_campaign[row.asset_group.campaign].append(row)

    # --- Audience lookup (resource_name -> display name), for signal labels ---
    audience_name_by_resource = {
        row.audience.resource_name: row.audience.name
        for row in search("SELECT audience.resource_name, audience.name FROM audience")
    }

    # --- Performance Max audience signals (targeting inputs per asset group) ---
    signal_rows = search(
        """
        SELECT asset_group_signal.asset_group,
               asset_group_signal.audience.audience,
               asset_group_signal.search_theme.text,
               campaign.status
        FROM asset_group_signal
        WHERE campaign.status = 'ENABLED'
        """
    )
    signals_by_asset_group: dict[str, list] = defaultdict(list)
    for row in signal_rows:
        signals_by_asset_group[row.asset_group_signal.asset_group].append(row)

    # --- Performance Max asset group assets (headlines, descriptions, images, video) ---
    aga_rows = search(
        """
        SELECT asset_group_asset.asset_group, asset_group_asset.field_type,
               asset.type, asset.name, asset.resource_name, asset.text_asset.text
        FROM asset_group_asset
        WHERE asset_group_asset.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
        """
    )
    assets_by_asset_group: dict[str, list] = defaultdict(list)
    for row in aga_rows:
        assets_by_asset_group[row.asset_group_asset.asset_group].append(row)

    # --- Extensions (campaign-level assets) ---
    extension_rows = search(
        """
        SELECT campaign_asset.field_type, campaign_asset.campaign, asset.type,
               asset.name, asset.resource_name, asset.sitelink_asset.link_text,
               asset.callout_asset.callout_text,
               asset.structured_snippet_asset.header,
               asset.structured_snippet_asset.values,
               asset.call_asset.country_code, asset.call_asset.phone_number,
               campaign.status
        FROM campaign_asset
        WHERE campaign_asset.status = 'ENABLED'
          AND campaign.status = 'ENABLED'
        """
    )
    extensions_by_campaign: dict[str, list] = defaultdict(list)
    for row in extension_rows:
        extensions_by_campaign[row.campaign_asset.campaign].append(row)

    # --- Render markdown ---
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(f"# Account snapshot: {account.descriptive_name}")
    lines.append("")
    lines.append(
        f"_Generated {now} — re-run `uv run scripts/snapshot.py {customer_id}` to refresh. "
        f"Only ENABLED campaigns are shown; paused/removed legacy campaigns are omitted._"
    )
    lines.append("")
    lines.append("## Account")
    lines.append("")
    lines.append(f"- Customer ID: `{account.id}`")
    lines.append(f"- Currency: {account.currency_code}")
    lines.append(f"- Time zone: {account.time_zone}")
    lines.append(f"- Status: {account.status.name}")
    if totals:
        lines.append(
            f"- This month so far: **{micros(totals.cost_micros):.2f} {account.currency_code}** spent, "
            f"{totals.clicks} clicks, {totals.impressions} impressions, "
            f"{totals.conversions:.1f} conversions (whole account, including any non-ENABLED campaigns)"
        )
    lines.append("")
    lines.append(f"## Active campaigns ({len(campaign_rows)})")
    lines.append("")
    lines.append("| Campaign | Channel | Cost | Clicks | Conversions |")
    lines.append("|---|---|---|---|---|")
    for row in campaign_rows:
        c, m = row.campaign, row.metrics
        lines.append(
            f"| [{c.name}](#{slugify(c.name)}-{c.id}) | {c.advertising_channel_type.name} | "
            f"{micros(m.cost_micros):.2f} {account.currency_code} | {m.clicks} | {m.conversions:.1f} |"
        )
    lines.append("")

    for row in campaign_rows:
        c = row.campaign
        b = row.campaign_budget
        m = row.metrics
        anchor_title = f"{c.name} (`{c.id}`)"
        lines.append(f"## {anchor_title}")
        lines.append("")
        lines.append(
            f"- Channel: {c.advertising_channel_type.name}"
            + (
                f" / {c.advertising_channel_sub_type.name}"
                if c.advertising_channel_sub_type.name != "UNKNOWN"
                else ""
            )
        )
        lines.append(f"- Bidding strategy: {c.bidding_strategy_type.name}")
        lines.append(
            f"- Budget: {b.name} — {micros(b.amount_micros):.2f} {account.currency_code} "
            f"({b.delivery_method.name})"
        )
        if c.start_date_time:
            lines.append(
                f"- Dates: {c.start_date_time}"
                + (f" → {c.end_date_time}" if c.end_date_time else " → (no end date)")
            )
        lines.append(
            f"- This month: {micros(m.cost_micros):.2f} {account.currency_code} spent, "
            f"{m.clicks} clicks, {m.impressions} impressions, {m.conversions:.1f} conversions"
        )

        # Extensions
        extensions = extensions_by_campaign.get(c.resource_name, [])
        if extensions:
            lines.append("")
            lines.append(f"**Extensions ({len(extensions)}):**")
            lines.append("")
            for ext_row in extensions:
                lines.append(
                    f"- [{ext_row.campaign_asset.field_type.name}] "
                    f"{asset_label(ext_row.asset)}"
                )

        # Performance Max -> asset groups, each with its own signals + assets
        asset_groups = asset_groups_by_campaign.get(c.resource_name, [])
        for ag_row in asset_groups:
            ag, agm = ag_row.asset_group, ag_row.metrics
            lines.append("")
            lines.append(
                f"**Asset group: {ag.name}** (`{ag.id}`, ad strength: {ag.ad_strength.name})"
            )
            lines.append(
                f"— {micros(agm.cost_micros):.2f} {account.currency_code}, "
                f"{agm.clicks} clicks, {agm.conversions:.1f} conversions"
            )

            signals = signals_by_asset_group.get(ag.resource_name, [])
            if signals:
                lines.append("")
                lines.append(f"_Audience signals ({len(signals)}):_")
                for sig_row in signals:
                    sig = sig_row.asset_group_signal
                    if sig.audience.audience:
                        name = audience_name_by_resource.get(
                            sig.audience.audience, sig.audience.audience
                        )
                        lines.append(f"- Audience: {name}")
                    elif sig.search_theme.text:
                        lines.append(f'- Search theme: "{sig.search_theme.text}"')

            assets = assets_by_asset_group.get(ag.resource_name, [])
            if assets:
                by_field_type: dict[str, list] = defaultdict(list)
                for a_row in assets:
                    by_field_type[a_row.asset_group_asset.field_type.name].append(
                        asset_label(a_row.asset)
                    )
                lines.append("")
                lines.append(f"_Assets ({len(assets)}):_")
                for field_type, labels in by_field_type.items():
                    lines.append(
                        f"- **{field_type}** ({len(labels)}): " + "; ".join(labels)
                    )

        # Search/Display -> ad groups with nested keywords + ads
        ad_groups = ad_groups_by_campaign.get(c.resource_name, [])
        for ag_row in ad_groups:
            ag, agm = ag_row.ad_group, ag_row.metrics
            lines.append("")
            lines.append(f"**Ad group: {ag.name}** (`{ag.id}`, {ag.type_.name})")
            lines.append(
                f"— {micros(agm.cost_micros):.2f} {account.currency_code}, "
                f"{agm.clicks} clicks, {agm.impressions} impressions"
            )

            kws = keywords_by_ad_group.get(ag.resource_name, [])
            if kws:
                lines.append("")
                lines.append("| Keyword | Match type | Clicks | Impr. | Cost |")
                lines.append("|---|---|---|---|---|")
                for kw_row in kws:
                    kw, kwm = kw_row.ad_group_criterion, kw_row.metrics
                    lines.append(
                        f"| {kw.keyword.text} | {kw.keyword.match_type.name} | "
                        f"{kwm.clicks} | {kwm.impressions} | {micros(kwm.cost_micros):.2f} |"
                    )

            ads = ads_by_ad_group.get(ag.resource_name, [])
            if ads:
                lines.append("")
                for ad_row in ads:
                    ad, adm = ad_row.ad_group_ad, ad_row.metrics
                    lines.append(
                        f"- Ad `{ad.ad.id}` ({ad.ad.type_.name}, "
                        f"policy: {ad.policy_summary.approval_status.name}) — "
                        f"{adm.clicks} clicks, {micros(adm.cost_micros):.2f} {account.currency_code}"
                    )
                    rsa = ad.ad.responsive_search_ad
                    if rsa.headlines:
                        headlines = " | ".join(h.text for h in rsa.headlines)
                        lines.append(f"  - Headlines: {headlines}")
                    if rsa.descriptions:
                        descriptions = " | ".join(d.text for d in rsa.descriptions)
                        lines.append(f"  - Descriptions: {descriptions}")

        lines.append("")

    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    out_path = SNAPSHOTS_DIR / f"{slugify(account.descriptive_name)}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"Wrote {out_path} ({len(campaign_rows)} active campaigns, "
        f"{len(ad_group_rows)} ad groups, {len(asset_group_rows)} asset groups, "
        f"{len(keyword_rows)} keywords, {len(ad_rows)} ads, {len(extension_rows)} extensions, "
        f"{len(signal_rows)} audience signals, {len(aga_rows)} asset group assets)"
    )


if __name__ == "__main__":
    main()
