const fs = require("fs");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "../../..");
const SAMPLE_DIR = path.join(REPO_ROOT, "tests", "fixtures", "sample_evidence");
const SAMPLE = path.join(SAMPLE_DIR, "test_disk.dd");

function ensureSampleEvidence() {
  if (fs.existsSync(SAMPLE) && fs.statSync(SAMPLE).size > 0) {
    return SAMPLE;
  }
  fs.mkdirSync(SAMPLE_DIR, { recursive: true });
  // Tiny synthetic image for registration/integrity; pipeline uses soft-acquire.
  fs.writeFileSync(SAMPLE, Buffer.from("DFAT-E2E-FAKE-DISK-IMAGE\n"));
  return SAMPLE;
}

/**
 * Copy the sample disk image into data/e2e for registration tests.
 * Returns an absolute path the backend can read.
 */
function prepareEvidenceFile(prefix = "e2e") {
  const source = ensureSampleEvidence();
  const destDir = path.join(REPO_ROOT, "data", "e2e");
  fs.mkdirSync(destDir, { recursive: true });
  const dest = path.join(destDir, `${prefix}-${Date.now()}.dd`);
  fs.copyFileSync(source, dest);
  return dest;
}

module.exports = {
  prepareEvidenceFile,
  SAMPLE,
  REPO_ROOT,
};
