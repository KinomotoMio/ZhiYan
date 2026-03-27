import PublicSharePlayer from "@/components/share/PublicSharePlayer";

interface SharePageProps {
  params: Promise<{ token: string }>;
}

export default async function SharePage({ params }: SharePageProps) {
  const resolved = await params;
  return <PublicSharePlayer token={resolved.token} />;
}
