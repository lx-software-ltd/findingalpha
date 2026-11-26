import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { fromWire, toWire, type WireContract } from "./wireFormat";

const casesPath = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../contracts/wire-format-cases.json");
const document = JSON.parse(readFileSync(casesPath, "utf8")) as {
  contract: WireContract;
  cases: { name: string; route?: string; value: unknown; wire: unknown }[];
};

describe("wire format cases", () => {
  it("ignores inherited keys such as constructor", () => {
    const contract = document.contract;
    expect(toWire({ constructor: 1 }, contract)).toEqual({ constructor: 1 });
    expect(fromWire({ constructor: 1 }, contract)).toEqual({ constructor: 1 });
  });

  it("round-trips every shared case", () => {
    for (const item of document.cases) {
      const wire = toWire(item.value, document.contract, item.route ?? "");
      expect(wire, item.name).toEqual(item.wire);
      expect(fromWire(wire, document.contract, item.route ?? ""), item.name).toEqual(item.value);
    }
  });
});
