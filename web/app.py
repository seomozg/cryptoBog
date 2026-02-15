from flask import Flask, render_template, request, jsonify
import logging
from datetime import datetime, timedelta
from database.db_manager import db_manager
from database.models import PriceSnapshot, TradeActivity, AISignal, TokenMetadata, TradePosition
from config.settings import Config

app = Flask(__name__)
config = Config()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/service_requests')
def get_service_requests():
    """Get history of requests to information services"""
    try:
        session = db_manager.get_session()

        # Get recent price snapshots
        price_snapshots = session.query(PriceSnapshot).order_by(PriceSnapshot.time.desc()).limit(100).all()

        # Get recent trade activity
        trade_activity = session.query(TradeActivity).order_by(TradeActivity.time.desc()).limit(100).all()

        # Get token metadata for symbols
        token_symbols = {}
        if len(price_snapshots) > 0 or len(trade_activity) > 0:
            token_ids = set()
            for ps in price_snapshots:
                token_ids.add(ps.token_id)
            for ta in trade_activity:
                token_ids.add(ta.token_id)

            if len(token_ids) > 0:  # Only query if we have token IDs
                tokens = session.query(TokenMetadata).filter(TokenMetadata.id.in_(token_ids)).all()
                token_symbols = {t.id: f"{t.name} ({t.symbol})" if t.name is not None and t.name != "" else t.symbol for t in tokens}

        session.close()

        return jsonify({
            'price_snapshots': [{
                'time': ps.time.isoformat() if ps.time is not None else None,
                'token_name': token_symbols.get(ps.token_id, f"Token {ps.token_id}"),
                'price_usd': str(ps.price_usd),
                'liquidity_usd': str(ps.liquidity_usd),
                'volume_24h': str(ps.volume_24h)
            } for ps in price_snapshots],
            'trade_activity': [{
                'time': ta.time.isoformat() if ta.time is not None else None,
                'token_name': token_symbols.get(ta.token_id, f"Token {ta.token_id}"),
                'buys_1h': ta.buys_1h,
                'sells_1h': ta.sells_1h,
                'volume_1h': str(ta.volume_1h)
            } for ta in trade_activity]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai_requests')
def get_ai_requests():
    """Get history of AI analysis requests"""
    try:
        session = db_manager.get_session()

        # Get recent AI signals
        ai_signals = session.query(AISignal).order_by(AISignal.generated_at.desc()).limit(100).all()

        session.close()

        return jsonify({
            'ai_signals': [{
                'id': signal.id,
                'generated_at': signal.generated_at.isoformat(),
                'asset': signal.asset,
                'action': signal.action,
                'entry_min': str(signal.entry_min),
                'entry_max': str(signal.entry_max),
                'probability': str(signal.probability),
                'confidence': str(signal.confidence),
                'reasoning': signal.reasoning,
                'sent_to_telegram': signal.sent_to_telegram
            } for signal in ai_signals]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/trading_history')
def get_trading_history():
    """Get history of trading positions"""
    try:
        session = db_manager.get_session()

        # Get all trading positions
        positions = session.query(TradePosition).order_by(TradePosition.opened_at.desc()).limit(100).all()

        session.close()

        return jsonify({
            'trading_history': [{
                'id': position.id,
                'symbol': position.symbol,
                'side': position.side,
                'quantity': str(position.quantity),
                'entry_price': str(position.entry_price),
                'stop_loss': str(position.stop_loss),
                'take_profit': str(position.take_profit),
                'exit_price': str(position.exit_price) if position.exit_price else None,
                'status': position.status,
                'opened_at': position.opened_at.isoformat() if position.opened_at else None,
                'closed_at': position.closed_at.isoformat() if position.closed_at else None,
                'pnl': str((position.exit_price - position.entry_price) * position.quantity) if position.exit_price else None,
                'pnl_percent': str(((position.exit_price - position.entry_price) / position.entry_price) * 100) if position.exit_price else None,
                'stop_loss_pct': str(((position.stop_loss - position.entry_price) / position.entry_price) * 100),
                'take_profit_pct': str(((position.take_profit - position.entry_price) / position.entry_price) * 100)
            } for position in positions]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/settings')
def settings() -> str:
    """Settings page"""
    return render_template('settings.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update settings"""
    if request.method == 'GET':
        return jsonify(config.get_all_user_settings())
    elif request.method == 'POST':
        try:
            data = request.json
            if config.save_user_settings(data):
                return jsonify({'status': 'settings_saved'})
            else:
                return jsonify({'status': 'error', 'error': 'Failed to save settings'}), 500
        except Exception as e:
            return jsonify({'status': 'error', 'error': str(e)}), 500

def create_app():
    """Application factory"""
    # Initialize database
    if db_manager.SessionLocal is None:
        db_manager.init_db()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)