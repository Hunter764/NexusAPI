"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const token = searchParams.get("token");
    
    if (token) {
      // Store the JWT token securely
      localStorage.setItem("nexus_token", token);
      
      // Redirect to the dashboard
      router.push("/dashboard");
    } else {
      // If no token, bounce back to demo/login
      router.push("/demo");
    }
  }, [router, searchParams]);

  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center text-white">
      <Loader2 className="w-10 h-10 animate-spin text-white/50 mb-4" />
      <h2 className="text-xl font-light tracking-tight">Authenticating...</h2>
      <p className="text-sm text-white/50 mt-2">Please wait while we log you in.</p>
    </div>
  );
}
