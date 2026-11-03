import type { NextApiRequest, NextApiResponse } from "next";
import { proxyApiRequest } from "@/lib/proxy";

export const config = {
  api: { bodyParser: false, responseLimit: false, externalResolver: true },
};
export default function handler(
  request: NextApiRequest,
  response: NextApiResponse,
) {
  return proxyApiRequest(
    request,
    response,
    process.env.OPENMOLSPEC_API_URL || "http://127.0.0.1:8000",
  );
}
