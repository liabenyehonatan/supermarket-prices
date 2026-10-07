import { redirect } from "next/navigation";

// Redirect root to default locale (Hebrew)
export default function RootPage() {
  redirect("/he");
}
