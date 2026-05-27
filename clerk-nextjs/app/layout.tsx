import "./globals.css";
import { ClerkProvider } from "@clerk/nextjs";

export const metadata = {
  title: "AI Builder · Auth",
  description: "Sign in or create an account for AI Builder.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorPrimary: "#6366f1",
          colorBackground: "#0d1219",
          colorText: "#e6edf3",
          colorTextSecondary: "#8b949e",
          colorInputBackground: "#0a0e16",
          colorInputText: "#e6edf3",
          colorNeutral: "#8b949e",
          colorDanger: "#ff7b72",
          colorSuccess: "#3fb950",
          colorWarning: "#d29922",
          borderRadius: "10px",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          fontSize: "14px",
        },
      }}
    >
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  );
}
