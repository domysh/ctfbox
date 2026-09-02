import type { NextConfig } from "next";

// The editor is published as a fully static bundle on GitHub Pages, under the
// /editor path of the CTFBox site. `output: "export"` keeps it a pile of files
// with no server behind it.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "/editor";

const nextConfig: NextConfig = {
    output: "export",
    basePath,
    assetPrefix: basePath,
    trailingSlash: true,
    images: { unoptimized: true },
    reactStrictMode: true,
};

export default nextConfig;
