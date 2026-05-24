// Patch starlight-blog's generated RSS feed.
//
// Why this exists:
//   - starlight-blog (0.26.x) passes Astro's `site` directly to @astrojs/rss
//     as the channel <link>, dropping the `base` path. Result: the feed's
//     channel <link> points at https://<host>/ instead of
//     https://<host>/<base>/blog/. Aggregators following the channel link
//     land on a 404.
//   - starlight-blog doesn't emit per-item author metadata. Frontmatter
//     `authors:` is used to render the author panel on the post page but
//     never surfaces into RSS as <dc:creator> or <author>.
//
// Both are upstream bugs. Until they're fixed there, we run this after
// `astro build` to patch dist/blog/rss.xml. Text-substitution on XML is
// brittle but the surface here is small and deterministic — the RSS file
// is generated, not human-edited, so the patterns we match don't drift.
//
// What this script does:
//   1. Adds xmlns:dc and xmlns:atom to the <rss> root.
//   2. Fixes channel <link> to include the base path.
//   3. Adds <atom:link rel="self"> for feed-validator hygiene.
//   4. Injects <dc:creator>Sergei Shmakov</dc:creator> into every <item>.

import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RSS_PATH = resolve(__dirname, "..", "dist", "blog", "rss.xml");

const SITE = "https://sergeyshmakov.github.io";
const BASE = "/mineru-runpod";
const FEED_CHANNEL_LINK = `${SITE}${BASE}/blog/`;
const FEED_SELF_HREF = `${SITE}${BASE}/blog/rss.xml`;
const AUTHOR_NAME = "Sergei Shmakov";

if (!existsSync(RSS_PATH)) {
	console.error(`[postbuild-rss] ${RSS_PATH} not found — was the site built?`);
	process.exit(1);
}

let xml = await readFile(RSS_PATH, "utf8");
const original = xml;

// 1. Add dc + atom namespaces to the <rss> root if missing.
xml = xml.replace(
	/<rss version="2.0"([^>]*)>/,
	(match, attrs) => {
		let next = attrs;
		if (!next.includes("xmlns:dc=")) {
			next += ' xmlns:dc="http://purl.org/dc/elements/1.1/"';
		}
		if (!next.includes("xmlns:atom=")) {
			next += ' xmlns:atom="http://www.w3.org/2005/Atom"';
		}
		return `<rss version="2.0"${next}>`;
	},
);

// 2. Fix the channel <link>. Match only the *channel* <link> (the one
// immediately following <description>) so per-item <link>s aren't touched.
xml = xml.replace(
	/(<\/description>)<link>[^<]*<\/link>/,
	`$1<link>${FEED_CHANNEL_LINK}</link>`,
);

// 3. Add atom:link self-reference inside <channel> if missing.
if (!xml.includes("<atom:link")) {
	xml = xml.replace(
		/(<language>[^<]*<\/language>)/,
		`$1<atom:link href="${FEED_SELF_HREF}" rel="self" type="application/rss+xml" />`,
	);
}

// 4. Insert <dc:creator> into every <item>. We add it right after the
// item's <pubDate> so item ordering stays predictable.
xml = xml.replace(
	/(<pubDate>[^<]*<\/pubDate>)(?!<dc:creator>)/g,
	`$1<dc:creator>${AUTHOR_NAME}</dc:creator>`,
);

if (xml === original) {
	console.log("[postbuild-rss] no changes needed — feed already patched?");
} else {
	await writeFile(RSS_PATH, xml, "utf8");
	console.log(`[postbuild-rss] patched ${RSS_PATH}`);
}
