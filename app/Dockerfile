FROM node:lts-alpine

WORKDIR /app

COPY . .

RUN npm install --production

EXPOSE 3000

CMD ["npm", "start"]
