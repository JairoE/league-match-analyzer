"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import {formatApiError} from "./format-api-error";
import {toApiError} from "./parse-api-error";
import type {ApiError} from "./types";

type ErrorState = Record<string, ApiError>;

type ErrorAction =
  | {type: "set"; scope: string; error: ApiError}
  | {type: "clear"; scope: string};

type ErrorStoreContextValue = {
  state: ErrorState;
  reportError: (scope: string, error: unknown) => void;
  clearError: (scope: string) => void;
};

const ErrorStoreContext = createContext<ErrorStoreContextValue | null>(null);

function errorReducer(state: ErrorState, action: ErrorAction): ErrorState {
  if (action.type === "set") {
    return {...state, [action.scope]: action.error};
  }

  if (!Object.prototype.hasOwnProperty.call(state, action.scope)) {
    return state;
  }

  const next = {...state};
  delete next[action.scope];
  return next;
}

export function AppErrorProvider({children}: {children: ReactNode}) {
  const [state, dispatch] = useReducer(errorReducer, {});

  const reportError = useCallback((scope: string, error: unknown) => {
    const normalized = toApiError(error);
    console.debug("[errors] report", {
      scope,
      status: normalized.status,
      detail: normalized.detail,
      riotStatus: normalized.riotStatus,
    });
    dispatch({type: "set", scope, error: normalized});
  }, []);

  const clearError = useCallback((scope: string) => {
    dispatch({type: "clear", scope});
  }, []);

  const value = useMemo(
    () => ({
      state,
      reportError,
      clearError,
    }),
    [state, reportError, clearError]
  );

  return (
    <ErrorStoreContext.Provider value={value}>{children}</ErrorStoreContext.Provider>
  );
}

export function useErrorStore(): ErrorStoreContextValue {
  const context = useContext(ErrorStoreContext);
  if (!context) {
    throw new Error("useErrorStore must be used within AppErrorProvider");
  }
  return context;
}

export function useAppError(scope: string) {
  const {state, reportError, clearError} = useErrorStore();
  const error = state[scope] ?? null;

  const reportScopedError = useCallback(
    (input: unknown) => {
      reportError(scope, input);
    },
    [reportError, scope]
  );

  const clearScopedError = useCallback(() => {
    clearError(scope);
  }, [clearError, scope]);

  return {
    error,
    errorMessage: formatApiError(error),
    reportError: reportScopedError,
    clearError: clearScopedError,
  };
}
