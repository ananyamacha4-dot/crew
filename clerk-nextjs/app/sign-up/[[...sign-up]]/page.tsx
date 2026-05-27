import { SignUp } from "@clerk/nextjs";
import { AuthShell } from "../../(auth)/AuthShell";
import { clerkAppearance } from "../../(auth)/clerkAppearance";

export const metadata = {
  title: "Create account · AI Builder",
};

export default function SignUpPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Spin up your first app in under a minute."
      footerText="Already have an account?"
      footerLinkText="Sign in"
      footerLinkHref="/sign-in"
    >
      <SignUp
        appearance={clerkAppearance}
        path="/sign-up"
        routing="path"
        signInUrl="/sign-in"
        fallbackRedirectUrl="/"
      />
    </AuthShell>
  );
}
