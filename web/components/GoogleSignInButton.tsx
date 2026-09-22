"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

// Google Identity Services types aren't bundled - this is the minimal shape
// we actually call. See https://developers.google.com/identity/gsi/web/reference/js-reference
interface GoogleCredentialResponse {
  credential: string;
}
interface GoogleIdConfiguration {
  client_id: string;
  callback: (response: GoogleCredentialResponse) => void;
}
interface GoogleButtonOptions {
  type?: "standard" | "icon";
  theme?: "outline" | "filled_blue" | "filled_black";
  size?: "large" | "medium" | "small";
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
  shape?: "rectangular" | "pill" | "circle" | "square";
  logo_alignment?: "left" | "center";
  width?: number;
}
interface GoogleAccountsId {
  initialize: (config: GoogleIdConfiguration) => void;
  renderButton: (parent: HTMLElement, options: GoogleButtonOptions) => void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } };
  }
}

// Google clamps the button's pixel width to this range - see
// https://developers.google.com/identity/gsi/web/reference/js-reference#width
const MIN_WIDTH = 200;
const MAX_WIDTH = 400;

interface Props {
  /** Receives the Google ID token; the caller decides where to POST it. Kept
   * caller-side so switching sign-in/sign-up doesn't re-render the widget. */
  onCredential: (credential: string) => void;
  disabled?: boolean;
}

/** "Continue with Google" - optional alongside email/password, never required.
 * Renders Google's own button (dark/pill, sized to its container) via Identity
 * Services. */
export function GoogleSignInButton({ onCredential, disabled }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLDivElement>(null);
  // The GSI script may already be loaded when this mounts (client-side nav, or
  // a remount after a tab switch). next/script's onLoad does NOT re-fire in
  // that case, which left the button invisible until a hard refresh - hence
  // onReady below plus this initial check.
  const [ready, setReady] = useState(
    () => typeof window !== "undefined" && !!window.google?.accounts?.id,
  );
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  // Keeps the callback current without re-rendering Google's widget.
  const handlerRef = useRef(onCredential);
  useEffect(() => {
    handlerRef.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!clientId || !ready) return;
    const wrap = wrapRef.current;
    const button = buttonRef.current;
    const gsi = window.google?.accounts.id;
    if (!wrap || !button || !gsi) return;

    gsi.initialize({
      client_id: clientId,
      callback: (response) => handlerRef.current(response.credential),
    });

    // Only re-render on an actual width change: observing the wrapper also
    // reports the height change the button itself causes, which would loop.
    let lastWidth = -1;
    const render = () => {
      const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(wrap.clientWidth)));
      if (width === lastWidth) return;
      lastWidth = width;
      button.replaceChildren();
      gsi.renderButton(button, {
        theme: "filled_black",
        size: "large",
        shape: "pill",
        text: "continue_with",
        logo_alignment: "left",
        width,
      });
    };
    render();

    const observer = new ResizeObserver(render);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [clientId, ready]);

  if (!clientId) return null;

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onReady={() => setReady(true)}
      />
      <div ref={wrapRef} className="google-btn-wrap" data-disabled={disabled ? "true" : undefined}>
        <div ref={buttonRef} />
      </div>
    </>
  );
}
