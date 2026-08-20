import { describe, expect, it } from "vitest";

import manifest from "./manifest";

describe("HelpSystem Carreira PWA", () => {
  it("é instalável com identidade e modo standalone", () => {
    const data = manifest();

    expect(data.name).toBe("HelpSystem Carreira");
    expect(data.short_name).toBe("HS Carreira");
    expect(data.display).toBe("standalone");
    expect(data.start_url).toBe("/");
    expect(data.lang).toBe("pt-BR");
  });

  it("mantém a identidade visual no carregamento", () => {
    const data = manifest();

    expect(data.background_color).toBe("#07111b");
    expect(data.theme_color).toBe("#07111b");
  });
});
