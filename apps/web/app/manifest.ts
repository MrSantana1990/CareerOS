import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "HelpSystem Carreira",
    short_name: "HS Carreira",
    description: "Radar inteligente e acompanhamento de oportunidades profissionais.",
    start_url: "/",
    display: "standalone",
    background_color: "#07111b",
    theme_color: "#07111b",
    orientation: "portrait-primary",
    categories: ["business", "productivity"],
    lang: "pt-BR",
  };
}
