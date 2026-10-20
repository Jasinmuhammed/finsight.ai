import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <div className="auth-page">
      <div className="auth-intro">
        <p className="eyebrow">WELCOME BACK</p>
        <h1>Sign in to FinSight</h1>
        <p className="muted">Access your saved screens and workspace.</p>
      </div>
      <AuthForm mode="login" />
    </div>
  );
}
