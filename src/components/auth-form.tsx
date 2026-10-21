"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

type AuthFormProps = {
  mode: "login" | "register";
};

type ApiError = {
  detail?: string | Array<{ msg?: string }>;
};

const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isRegistration = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (isRegistration && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);
    try {
      let response: Response;
      try {
        response = await fetch(
          `${apiBase}/auth/${isRegistration ? "register" : "login"}`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          },
        );
      } catch {
        throw new Error(
          "Unable to connect to the API. Check that the API is running and try again.",
        );
      }
      if (!response.ok) {
        const body = (await response.json()) as ApiError;
        const detail = Array.isArray(body.detail)
          ? body.detail.map((item) => item.msg).filter(Boolean).join(" ")
          : body.detail;
        throw new Error(detail || `Request failed (${response.status}).`);
      }
      router.replace("/");
      router.refresh();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to sign in right now.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="auth-card" onSubmit={submit}>
      <label className="field">
        <span>Email address</span>
        <input
          autoComplete="email"
          autoFocus
          maxLength={320}
          onChange={(event) => setEmail(event.target.value)}
          required
          type="email"
          value={email}
        />
      </label>
      <label className="field">
        <span>Password</span>
        <input
          autoComplete={isRegistration ? "new-password" : "current-password"}
          maxLength={128}
          minLength={12}
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
        {isRegistration && <small>Use at least 12 characters.</small>}
      </label>
      {isRegistration && (
        <label className="field">
          <span>Confirm password</span>
          <input
            autoComplete="new-password"
            maxLength={128}
            minLength={12}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            type="password"
            value={confirmPassword}
          />
        </label>
      )}
      {error && <p className="auth-error" role="alert">{error}</p>}
      <button className="primary-button auth-submit" disabled={submitting} type="submit">
        {submitting ? "Please wait…" : isRegistration ? "Create account" : "Sign in"}
      </button>
      <p className="auth-switch">
        {isRegistration ? "Already have an account? " : "New to FinSight? "}
        <Link href={isRegistration ? "/login" : "/register"}>
          {isRegistration ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </form>
  );
}
