import { fetch } from 'sdk';
import { EC2_API_URL, API_SECRET } from './config.js';
export async function enqueueOnEc2(payload) {
  const res = await fetch(`${EC2_API_URL}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Secret': API_SECRET },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`EC2 API ${res.status}: ${await res.text()}`);
  return await res.json(); // { job_id, position, status }
}
export async function jobStatus(jobId) {
  const res = await fetch(`${EC2_API_URL}/jobs/${jobId}`, { headers: { 'X-API-Secret': API_SECRET } });
  if (!res.ok) throw new Error(`EC2 API ${res.status}`);
  return await res.json();
}
