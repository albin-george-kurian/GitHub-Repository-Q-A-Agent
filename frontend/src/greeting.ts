import { useEffect, useState } from "react";

export function greetingFor(hour: number): string {
  if (hour >= 5 && hour < 12) return "Good morning, coder";
  if (hour >= 12 && hour < 17) return "Good afternoon, coder";
  if (hour >= 17 && hour < 22) return "Good evening, coder";
  return "Burning the midnight oil, coder?";
}

/** Time-of-day greeting that stays correct if the page is left open across a boundary. */
export function useGreeting(): string {
  const [hour, setHour] = useState(() => new Date().getHours());
  useEffect(() => {
    const id = window.setInterval(() => setHour(new Date().getHours()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  return greetingFor(hour);
}
