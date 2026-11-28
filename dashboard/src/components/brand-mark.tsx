import Image from "next/image";

export function BrandMark({ size = 34 }: { size?: number }) {
  return <Image src="/brand/somnia.svg" width={size} height={size} alt="" className="shrink-0" />;
}
