import assert from "node:assert/strict";
import { test } from "node:test";
import { rowsFromImageTsv } from "../src/app/settings/investors/image-ocr";

const header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext";

function word(text: string, x: number, y: number, number: number) {
  return `5\t1\t1\t1\t${Math.round(y / 40)}\t${number}\t${x}\t${y}\t60\t20\t93\t${text}`;
}

test("extracts table columns from a clear account screenshot", () => {
  const tsv = [header,
    ...[
      ["Name", 10], ["PAN", 200], ["Type", 330], ["DPID", 420],
      ["CLIENT", 520], ["ID", 590], ["UPI", 700], ["ID", 750],
      ["Account", 900], ["Number", 980], ["Bank", 1100], ["Name", 1160],
    ].map(([text, x], index) => word(String(text), Number(x), 20, index + 1)),
    ...[
      ["Example", 10], ["Investor", 85], ["ABCDE1234F", 200], ["CDSL", 330],
      ["12345678", 520], ["example@upi", 700], ["9876543210", 900], ["Test", 1100], ["Bank", 1160],
    ].map(([text, x], index) => word(String(text), Number(x), 60, index + 1)),
  ].join("\n");
  const rows = rowsFromImageTsv(tsv);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0], {
    Name: "Example Investor", PAN: "ABCDE1234F", Type: "CDSL", DPID: "",
    "CLIENT ID": "12345678", "UPI ID": "example@upi", "Account Number": "9876543210",
    "Bank Name": "Test Bank",
  });
});

test("extracts an image row without bank columns for import defaults", () => {
  const tsv = [header,
    ...[
      ["Example", 10], ["Investor", 85], ["ABCDE1234F", 200], ["CDSL", 330],
      ["12345678", 520], ["example@upi", 700],
    ].map(([text, x], index) => word(String(text), Number(x), 60, index + 1)),
  ].join("\n");
  const [row] = rowsFromImageTsv(tsv);
  assert.equal(row.Name, "Example Investor");
  assert.equal(row.PAN, "ABCDE1234F");
  assert.equal(row["CLIENT ID"], "12345678");
  assert.equal(row["UPI ID"], "example@upi");
  assert.equal(row["Account Number"], "");
  assert.equal(row["Bank Name"], "");
  assert.equal(rowsFromImageTsv(tsv.split("\n").slice(1).join("\n"))[0].PAN, "ABCDE1234F");
});
