// Dev-only demo survey for working on the survey page without a real link.
// Open /sondage/demo on the Vite dev server (`npm run dev`, also through an
// ngrok tunnel to it). Production builds drop it (import.meta.env.DEV is
// false there). Nothing is fetched or saved: submitting only shows the
// thank-you screen.
import type { SurveyPublic } from '../api/schema.d.ts';

export const DEMO_SURVEY_TOKEN = 'demo';

export function isDemoSurvey(token: string): boolean {
  return import.meta.env.DEV && token === DEMO_SURVEY_TOKEN;
}

export const DEMO_SURVEY: SurveyPublic = {
  token: DEMO_SURVEY_TOKEN,
  request_id: -1,
  building_address: '1240 chemin Sainte-Foy, Québec',
  technician_name: 'Marc Tremblay',
  already_submitted: false,
};
