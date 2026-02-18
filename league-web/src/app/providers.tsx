"use client";

import type {ReactNode} from "react";
import {AppErrorProvider} from "../lib/errors/error-store";

export default function Providers({children}: {children: ReactNode}) {
  return <AppErrorProvider>{children}</AppErrorProvider>;
}
