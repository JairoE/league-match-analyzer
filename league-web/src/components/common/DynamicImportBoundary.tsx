"use client";

import {Component} from "react";
import type {ErrorInfo, ReactNode} from "react";

type Props = {
  children: ReactNode;
  fallback: ReactNode;
  resetKey?: string | number;
};

type State = {hasError: boolean};

export class DynamicImportBoundary extends Component<Props, State> {
  state: State = {hasError: false};

  static getDerivedStateFromError(): State {
    return {hasError: true};
  }

  componentDidUpdate(prevProps: Props) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.hasError) {
      this.setState({hasError: false});
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[DynamicImportBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}
