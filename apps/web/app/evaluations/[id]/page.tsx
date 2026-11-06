import { Lab } from "../../../components/lab";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <Lab page="run" id={id} />;
}
