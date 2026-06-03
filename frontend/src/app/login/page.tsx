"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.login(login, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? "Неверный логин или пароль" : "Ошибка сети");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>Вход</h2>
        <form onSubmit={onSubmit}>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Логин</div>
            <input className="input" value={login} onChange={(e) => setLogin(e.target.value)} />
          </div>
          <div style={{ margin: "14px 0" }}>
            <div className="label">Пароль</div>
            <input className="input" type="password" value={password}
              onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ marginTop: 12, width: "100%" }}>Войти</button>
        </form>
        <p style={{ marginTop: 16 }}>Нет аккаунта? <a href="/register">Регистрация</a></p>
      </div>
    </div>
  );
}
