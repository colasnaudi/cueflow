"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type ButtonProps = React.ComponentProps<typeof Button>;

/** Two-step button: the first click arms it, the second (within 4 s) runs `onConfirm`. No browser dialog. */
export function ConfirmButton({
  confirmLabel,
  onConfirm,
  children,
  ...props
}: Omit<ButtonProps, "onClick"> & { confirmLabel: React.ReactNode; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(timer);
  }, [armed]);

  return (
    <Button
      {...props}
      variant={armed ? "destructive" : props.variant}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onConfirm();
        } else {
          setArmed(true);
        }
      }}
    >
      {armed ? confirmLabel : children}
    </Button>
  );
}
