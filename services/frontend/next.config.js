/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
  // Production optimizations
  ...(process.env.NODE_ENV === 'production' && {
    compress: true,
  }),
  // Standalone output only for Docker deployments (use NEXT_STANDALONE=true)
  ...(process.env.NEXT_STANDALONE === 'true' && {
    output: 'standalone',
  }),
};

module.exports = nextConfig;

