import { useState } from 'react';
import { supabase } from '../../lib/supabase';
import BrandMark from '../../components/BrandMark';
import styles from './index.module.css';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { data, error: err } = await supabase.auth.signInWithPassword({ email, password });
      if (err) { setError(err.message); return; }
      if (!data.session) { setError('Connexion échouée — aucune session reçue.'); return; }
    } catch {
      setError('Connexion échouée — veuillez réessayer.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <BrandMark product="Maintenance" />
        </div>

        <div className={styles.intro}>
          <h1 className={styles.title}>Connexion</h1>
          <p className={styles.subtitle}>Accédez au portail de répartition et d'entretien.</p>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="email">
              Courriel de l'entreprise
            </label>
            <input
              id="email"
              type="email"
              className={styles.input}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">
              Mot de passe
            </label>
            <input
              id="password"
              type="password"
              className={styles.input}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && <p className={styles.error} role="alert">{error}</p>}

          <button type="submit" className={styles.btn} disabled={loading}>
            {loading ? 'Connexion…' : 'Se connecter'}
          </button>
        </form>

        <p className={styles.note}>
          Accès lié au courriel de l'entreprise, révocable centralement.
        </p>
      </div>
    </div>
  );
}
