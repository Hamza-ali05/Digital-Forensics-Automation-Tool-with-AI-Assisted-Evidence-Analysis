/** Seeded credentials from ``scripts/seed_dev_data.py``. */
module.exports = {
  admin: {
    username: "admin",
    password: "Admin!Pass#2026",
  },
  investigator: {
    username: "investigator1",
    password: "Invest!Pass#2026",
  },
  analyst: {
    username: "analyst1",
    password: "Analyst!Pass#2026",
  },
  API_BASE: process.env.DFAT_API_BASE || "http://127.0.0.1:8000/api/v1",
};
