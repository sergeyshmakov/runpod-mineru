import sitemap from "@astrojs/sitemap";
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";
import starlightBlog from "starlight-blog";

const REPO_URL = "https://github.com/sergeyshmakov/runpod-mineru";

export default defineConfig({
	site: "https://sergeyshmakov.github.io",
	base: "/runpod-mineru",
	integrations: [
		starlight({
			title: "runpod-mineru",
			description:
				"Serverless MinerU 2.5 PDF parser on RunPod. Scales to zero, ~$0.0001 per page.",
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
					items: ["getting-started/overview"],
				},
				{
					label: "Guides",
					items: ["guides/choosing-gpu"],
				},
			],
			head: [
				{
					tag: "meta",
					attrs: { property: "og:image", content: "/runpod-mineru/og-default.png" },
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
