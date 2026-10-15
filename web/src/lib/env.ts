import "server-only";

export interface ServerEnv {
  apiUrl: string;
  adminToken: string;
}

function required(name: "SOMNIA_API_URL" | "SOMNIA_ADMIN_TOKEN"): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set (server-side env only)`);
  }
  return value;
}

export function serverEnv(): ServerEnv {
  return { apiUrl: required("SOMNIA_API_URL"), adminToken: required("SOMNIA_ADMIN_TOKEN") };
}
