import "server-only";

export function getSomniaApiUrl() {
  const url = process.env.SOMNIA_API_URL?.trim();
  if (!url) return null;

  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}
