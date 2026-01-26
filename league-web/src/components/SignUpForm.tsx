"use client";

import AuthForm from "./AuthForm";
import type { UserSession } from "../lib/types/user";

type SignUpFormProps = {
  onAuthSuccess: (user: UserSession) => void;
};

export default function SignUpForm({ onAuthSuccess }: SignUpFormProps) {
  return (
    <AuthForm
      title="Sign up"
      ctaLabel="Create account"
      endpoint="/users/sign_up"
      onAuthSuccess={onAuthSuccess}
    />
  );
}
