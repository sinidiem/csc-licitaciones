import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import Nav from "./Nav";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const store = await cookies();
  const token = store.get("access_token");
  if (!token) redirect("/login");
  return (
    <>
      <Nav />
      <main>{children}</main>
    </>
  );
}