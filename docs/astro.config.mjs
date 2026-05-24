import sitemap from "@astrojs/sitemap";
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";
import starlightBlog from "starlight-blog";

const REPO_URL = "https://github.com/sergeyshmakov/mineru-runpod";

export default defineConfig({
	site: "https://sergeyshmakov.github.io",
	base: "/mineru-runpod",
	integrations: [
		starlight({
			title: "mineru-runpod",
			description:
				"Open-source template to deploy MinerU (3.1 runtime, MinerU 2.5 Pro VLM) onto RunPod Serverless in two clicks. Self-hosted endpoint, scales to zero, ~$0.0003 per page on 24 GB Ampere.",
			favicon: "/favicon.png",
			customCss: ["./src/styles/custom.css"],
			social: [{ icon: "github", label: "GitHub", href: REPO_URL }],
			editLink: {
				baseUrl: `${REPO_URL}/edit/main/docs/`,
			},
			lastUpdated: true,
			tableOfContents: { minHeadingLevel: 2, maxHeadingLevel: 3 },
			expressiveCode: {
				themes: ["github-dark", "github-light"],
				styleOverrides: { borderRadius: "0.375rem" },
			},
			plugins: [
				starlightBlog({
					title: "Blog",
					authors: {
						sergei: {
							name: "Sergei Shmakov",
							url: "https://github.com/sergeyshmakov",
							picture: "https://github.com/sergeyshmakov.png",
						},
					},
				}),
			],
			sidebar: [
				{
					label: "Getting Started",
					items: [
						"getting-started/overview",
						"getting-started/deploy",
						"getting-started/clients",
					],
				},
				{
					label: "Guides",
					items: [
						"guides/choosing-gpu",
						"guides/input-formats",
						"guides/output-modes",
						"guides/network-volumes",
						"guides/troubleshooting",
					],
				},
				{
					label: "Reference",
					items: ["reference/api"],
				},
			],
			head: [
				{
					tag: "style",
					attrs: { "data-rm-critical-bg": "" },
					content:
						"html,body{background-color:#090236;}html[data-theme='light'],html[data-theme='light'] body{background-color:#fff;}",
				},
				{
					tag: "meta",
					attrs: { property: "og:image", content: "/mineru-runpod/og-default.png" },
				},
				{
					tag: "meta",
					attrs: { name: "twitter:card", content: "summary_large_image" },
				},
			],
		}),
		sitemap(),
	],
});
