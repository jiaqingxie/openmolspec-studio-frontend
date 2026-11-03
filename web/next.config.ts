import type { NextConfig } from "next";

// API transport lives in pages/api so the upstream address is read at runtime,
// including in standalone builds and containers.
const config: NextConfig = { output: "standalone" };
export default config;
