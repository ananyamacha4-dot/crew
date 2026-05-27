import { SignIn } from "@clerk/nextjs";
import { AuthShell } from "../../(auth)/AuthShell";
import { clerkAppearance } from "../../(auth)/clerkAppearance";

export const metadata = {
  title: "Sign in · AI Builder",
};

export default function SignInPage() {
  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to continue building."
      footerText="New here?"
      footerLinkText="Create an account"
      footerLinkHref="/sign-up"
    >
      <SignIn
        appearance={clerkAppearance}
        path="/sign-in"
        routing="path"
        signUpUrl="/sign-up"
        fallbackRedirectUrl="/"
      />
    </AuthShell>
  );
}
