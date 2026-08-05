# Use official Node.js Slim image
FROM node:20-slim

# Set working directory
WORKDIR /app

# Copy package configurations and change ownership to node user
COPY --chown=node:node package.json /app/

# Install application dependencies
RUN npm install

# Copy application source code and change ownership to node user
COPY --chown=node:node . /app

# Switch to the non-root node user
USER node

# Expose Vite service port
EXPOSE 5173

# Start development server
CMD ["npm", "run", "dev"]
