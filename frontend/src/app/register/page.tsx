"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.register(login, password, accessCode);
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) setError("Неверный код доступа");
        else if (err.status === 409) setError("Логин уже занят");
        else setError(err.message);
      } else setError("Ошибка сети");
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto" }}>
      <div className="card">
        <h2>Регистрация</h2>
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
          <div style={{ margin: "14px 0" }}>
            <div className="label">Код доступа</div>
            <input className="input" value={accessCode} onChange={(e) => setAccessCode(e.target.value)} />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn" type="submit" style={{ marginTop: 12, width: "100%" }}>Зарегистрироваться</button>
        </form>
        <p style={{ marginTop: 16 }}>Уже есть аккаунт? <a href="/login">Вход</a></p>
      </div>
    </div>
  );
}
