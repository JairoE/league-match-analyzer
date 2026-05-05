import type {NextConfig} from "next";

const nextConfig: NextConfig = {
  experimental: {
    reactCompiler: {
      compilationMode: "annotation",
    },
  },
};

export default nextConfig;
