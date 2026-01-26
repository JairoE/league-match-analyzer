"use client";

import AuthForm from "./AuthForm";
import type { UserSession } from "../lib/types/user";

type SignInFormProps = {
  onAuthSuccess: (user: UserSession) => void;
};

export default function SignInForm({ onAuthSuccess }: SignInFormProps) {
  return (
    <AuthForm
      title="Sign in"
      ctaLabel="Sign in"
      endpoint="/users/sign_in"
      onAuthSuccess={onAuthSuccess}
    />
  );
}
