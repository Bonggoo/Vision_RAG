import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 정적 export: FastAPI가 단일 오리진에서 서빙(통합 오리진). next dev에는 영향 없음.
  output: "export",
  // 정적 서버(FastAPI StaticFiles)에서 /path → /path/index.html 매핑이 자연스럽도록
  trailingSlash: true,
  allowedDevOrigins: ["172.20.10.7", "192.168.219.109"],
};

export default nextConfig;
