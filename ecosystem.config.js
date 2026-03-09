// PM2 Ecosystem Config — IDX AI Trading Assistant
// Jalankan: pm2 start ecosystem.config.js

module.exports = {
    apps: [{
        name: 'ai-saham',
        script: 'bot/telegram_bot.py',
        args: '--run',
        interpreter: '/root/ai-saham-analyst-bot/venv/bin/python3',
        cwd: '/root/ai-saham-analyst-bot',

        // Auto restart
        autorestart: true,
        watch: false,
        max_restarts: 10,
        restart_delay: 5000,

        // Memory limit (VPS 2GB, limit bot ke 800MB)
        max_memory_restart: '800M',

        // Log
        error_file: '/root/ai-saham-analyst-bot/logs/pm2-error.log',
        out_file: '/root/ai-saham-analyst-bot/logs/pm2-out.log',
        log_date_format: 'YYYY-MM-DD HH:mm:ss',
        merge_logs: true,

        // Environment
        env: {
            TZ: 'Asia/Jakarta',
        },
    }]
};
