/**
 * The per-account fixes-log sheet the platform creates in the user's Drive
 * (spec account-connection, "The platform creates one fixes-log sheet per
 * account"). Works with a Google access token that carries `drive.file`;
 * `fetchImpl` is injectable for tests.
 */
import contract from "../../db/contracts/fixes-log-header.json";

import { formatCustomerId } from "@/lib/format";

export const FIXES_WORKSHEET: string = contract.worksheet;
export const FIXES_HEADER: readonly string[] = contract.header;

type Fetch = typeof fetch;

export function fixesSheetTitle(displayName: string, customerId: string): string {
  const name = displayName.trim() || "Google Ads";
  return `Adsmigo fixes log — ${name} (${formatCustomerId(customerId)})`;
}

/** The Sheets API request body: one tab with a frozen bold header row. */
export function spreadsheetBody(title: string) {
  return {
    properties: { title },
    sheets: [
      {
        properties: {
          title: FIXES_WORKSHEET,
          gridProperties: { frozenRowCount: 1, columnCount: FIXES_HEADER.length },
        },
        data: [
          {
            startRow: 0,
            startColumn: 0,
            rowData: [
              {
                values: FIXES_HEADER.map((column) => ({
                  userEnteredValue: { stringValue: column },
                  userEnteredFormat: { textFormat: { bold: true } },
                })),
              },
            ],
          },
        ],
      },
    ],
  };
}

/** Creates the spreadsheet and returns its id. */
export async function createFixesSheet(
  accessToken: string,
  title: string,
  fetchImpl: Fetch = fetch,
): Promise<string> {
  const res = await fetchImpl("https://sheets.googleapis.com/v4/spreadsheets", {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json" },
    body: JSON.stringify(spreadsheetBody(title)),
  });
  const body = (await res.json().catch(() => ({}))) as { spreadsheetId?: string };
  if (!res.ok || !body.spreadsheetId) throw new Error(`Sheets API ${res.status}: spreadsheet not created`);
  return body.spreadsheetId;
}

export type SheetState = "ok" | "missing";

/**
 * Is the sheet still there? Deleted, trashed or unreachable (404/403) counts
 * as missing; other failures throw so a Google outage is not shown as a
 * missing sheet.
 */
export async function probeFixesSheet(
  accessToken: string,
  spreadsheetId: string,
  fetchImpl: Fetch = fetch,
): Promise<SheetState> {
  const res = await fetchImpl(
    `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(spreadsheetId)}?fields=id,trashed`,
    { headers: { authorization: `Bearer ${accessToken}` } },
  );
  if (res.status === 404 || res.status === 403) return "missing";
  if (!res.ok) throw new Error(`Drive API ${res.status}`);
  const body = (await res.json()) as { trashed?: boolean };
  return body.trashed ? "missing" : "ok";
}

export function sheetUrl(spreadsheetId: string): string {
  return `https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit`;
}
