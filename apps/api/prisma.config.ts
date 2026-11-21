import { defineConfig } from 'prisma/config';

export default defineConfig({
  schema: './prisma/schema.prisma',
  migrations: {
    path: './prisma/migrations',
  },
  client: {
    generator: 'client',
  },
  datasources: {
    db: {
      url: process.env.DATABASE_URL || 'mysql://root:postgres@localhost:3306/email_orchestrator',
    },
  },
});