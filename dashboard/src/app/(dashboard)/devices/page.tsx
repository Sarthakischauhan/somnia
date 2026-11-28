import { DeviceManager } from "@/components/device-manager";
import { somnia, unwrap } from "@/lib/api/client";

export const dynamic = "force-dynamic";

export default async function DevicesPage() {
  const api = await somnia();
  const devices = unwrap(await api.GET("/v1/devices"));

  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Devices</h1>
        <p className="text-sm text-muted-foreground">
          Each coding agent gets its own token. Revoking a token immediately blocks that device.
        </p>
      </div>
      <DeviceManager devices={devices} />
    </section>
  );
}
