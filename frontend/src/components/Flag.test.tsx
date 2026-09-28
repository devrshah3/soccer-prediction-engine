import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Flag } from "./Flag";

const markup = (country: string | null) => render(<Flag country={country} />).container.innerHTML;

describe("Flag", () => {
  it("draws the country's own real flag, titled with its name", () => {
    for (const country of ["Spain", "Italy", "Germany", "France", "Serbia"]) {
      const html = markup(country);
      expect(html).toContain(`<title>${country}</title>`);
    }
  });

  it("gives England St George's Cross, not the Union Flag - and Scotland its own", () => {
    const england = markup("England");
    expect(england).toContain("<title>England</title>");
    expect(england).not.toBe(markup("United Kingdom"));
    expect(markup("Scotland")).not.toBe(england);
    expect(markup("Scotland")).toContain("<title>Scotland</title>");
  });

  it("uses a neutral drawn placeholder (no emoji, no title) for international/unknown", () => {
    for (const country of [null, "Atlantis"]) {
      const html = markup(country);
      expect(html).not.toContain("<title>");
      expect(html).toContain("<svg");
      expect(html).not.toMatch(/[\u{1F1E6}-\u{1F1FF}]/u);
    }
  });
});
