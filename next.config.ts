import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  reactStrictMode: true,
  transpilePackages: ["ketcher-react", "react-contexify"],
};

export default nextConfig;
