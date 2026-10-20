import { AuthForm } from "@/components/auth-form";

export default function RegisterPage() {
  return (
    <div className="auth-page">
      <div className="auth-intro">
        <p className="eyebrow">CREATE ACCOUNT</p>
        <h1>Your workspace starts here</h1>
        <p className="muted">Create an account to save your screens.</p>
      </div>
      <AuthForm mode="register" />
    </div>
  );
}
