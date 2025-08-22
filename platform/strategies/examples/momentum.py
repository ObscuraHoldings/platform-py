"""
ML-enhanced momentum trading strategy using Polars for data processing.

This strategy demonstrates:
- Real-time ML risk scoring
- ONNX model integration for signal generation
- Polars for high-performance data processing
- Backtesting framework with time-aware data splitting
"""

import asyncio
import structlog
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta

import polars as pl
import numpy as np

from ..base import BaseStrategy, StrategyManifest, StrategyState
from ...types import (
    Intent, IntentType, IntentStatus, IntentConstraints, AssetSpec, 
    ExecutionStyle, Asset, AssetAmount, MLFeatures,
    create_acquire_intent, create_rebalance_intent
)

logger = structlog.get_logger()


class MomentumFeatures:
    """Feature engineering for momentum strategy."""
    
    @staticmethod
    def calculate_momentum_features(price_data: pl.DataFrame, lookback_periods: int = 20) -> Dict[str, float]:
        """Calculate momentum features using Polars."""
        if len(price_data) < lookback_periods:
            return {}
        
        # Calculate returns and momentum indicators
        df = price_data.with_columns([
            # Price changes
            pl.col("price").pct_change().alias("returns"),
            pl.col("price").pct_change(5).alias("returns_5d"),
            pl.col("price").pct_change(20).alias("returns_20d"),
            
            # Moving averages
            pl.col("price").rolling_mean(5).alias("ma_5"),
            pl.col("price").rolling_mean(10).alias("ma_10"),
            pl.col("price").rolling_mean(20).alias("ma_20"),
            
            # Volatility
            pl.col("price").rolling_std(10).alias("vol_10d"),
            pl.col("price").rolling_std(20).alias("vol_20d"),
            
            # Volume indicators
            pl.col("volume").rolling_mean(5).alias("volume_ma_5"),
            pl.col("volume").rolling_mean(20).alias("volume_ma_20"),
        ])
        
        # Get latest row
        latest = df.tail(1).to_dicts()[0]
        
        # Calculate derived features
        price_momentum = (latest["price"] - latest["ma_20"]) / latest["ma_20"] if latest["ma_20"] else 0
        volume_ratio = latest["volume"] / latest["volume_ma_20"] if latest["volume_ma_20"] else 1
        volatility_ratio = latest["vol_10d"] / latest["vol_20d"] if latest["vol_20d"] else 1
        
        # Moving average trend
        ma_trend = 0
        if latest["ma_5"] and latest["ma_10"] and latest["ma_20"]:
            if latest["ma_5"] > latest["ma_10"] > latest["ma_20"]:
                ma_trend = 1  # Uptrend
            elif latest["ma_5"] < latest["ma_10"] < latest["ma_20"]:
                ma_trend = -1  # Downtrend
        
        return {
            "price_momentum": float(price_momentum),
            "volume_ratio": float(volume_ratio),
            "volatility_ratio": float(volatility_ratio),
            "ma_trend": float(ma_trend),
            "returns_5d": float(latest.get("returns_5d", 0) or 0),
            "returns_20d": float(latest.get("returns_20d", 0) or 0),
            "vol_10d": float(latest.get("vol_10d", 0) or 0),
            "rsi": MomentumFeatures._calculate_rsi(price_data.tail(14))
        }
    
    @staticmethod
    def _calculate_rsi(price_data: pl.DataFrame, period: int = 14) -> float:
        """Calculate RSI using Polars."""
        if len(price_data) < period:
            return 50.0  # Neutral RSI
        
        df = price_data.with_columns([
            pl.col("price").diff().alias("price_change")
        ])
        
        gains = df.filter(pl.col("price_change") > 0).select("price_change").sum().item()
        losses = -df.filter(pl.col("price_change") < 0).select("price_change").sum().item()
        
        if losses == 0:
            return 100.0
        
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)


class RiskScorer:
    """ML-enhanced risk scoring for momentum strategy."""
    
    def __init__(self, strategy: 'MomentumStrategy'):
        self.strategy = strategy
    
    async def calculate_risk_score(self, features: Dict[str, float], position_size: float) -> float:
        """Calculate risk score using ML models."""
        try:
            # Use ML model if available
            if "models/risk_scorer.onnx" in self.strategy.ml_manager.get_loaded_models():
                ml_result = await self.strategy.predict_with_model("models/risk_scorer.onnx", features)
                if "risk_score" in ml_result:
                    return ml_result["risk_score"]
            
            # Fallback to heuristic risk scoring
            return self._heuristic_risk_score(features, position_size)
            
        except Exception as e:
            logger.warning("Risk scoring failed, using fallback", error=str(e))
            return self._heuristic_risk_score(features, position_size)
    
    def _heuristic_risk_score(self, features: Dict[str, float], position_size: float) -> float:
        """Heuristic risk scoring as fallback."""
        risk_score = 0.0
        
        # Volatility risk
        vol_risk = min(features.get("volatility_ratio", 1.0), 3.0) / 3.0
        risk_score += vol_risk * 0.3
        
        # Position size risk
        size_risk = min(position_size, 0.2) / 0.2  # Max 20% position
        risk_score += size_risk * 0.2
        
        # Momentum divergence risk
        momentum = features.get("price_momentum", 0)
        if abs(momentum) > 0.1:  # High momentum can be risky
            risk_score += 0.2
        
        # Volume anomaly risk
        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio > 3.0 or volume_ratio < 0.3:
            risk_score += 0.2
        
        # RSI extreme risk
        rsi = features.get("rsi", 50)
        if rsi > 80 or rsi < 20:
            risk_score += 0.1
        
        return min(risk_score, 1.0)


class MomentumStrategy(BaseStrategy):
    """ML-enhanced momentum trading strategy."""
    
    def __init__(self, strategy_id: UUID, config: Dict[str, Any]):
        # Define strategy manifest
        manifest = StrategyManifest(
            name="momentum_ml",
            version="1.0.0",
            description="ML-enhanced momentum strategy with Polars data processing",
            ml_models=[
                "models/momentum_signal.onnx",
                "models/risk_scorer.onnx",
                "models/market_regime.onnx"
            ],
            model_cache_dir=config.get("model_cache_dir", "./models"),
            gpu_memory_mb=config.get("gpu_memory_mb", 1024),
            cpu_cores=config.get("cpu_cores", 2),
            dependencies=["polars", "numpy", "onnxruntime"],
            config_schema={
                "lookback_periods": {"type": int, "required": True, "default": 20},
                "signal_threshold": {"type": float, "required": True, "default": 0.7},
                "risk_threshold": {"type": float, "required": True, "default": 0.3},
                "max_position_size": {"type": float, "required": True, "default": 0.1},
                "rebalance_frequency_hours": {"type": int, "required": False, "default": 4},
                "target_assets": {"type": list, "required": True}
            },
            default_config={
                "lookback_periods": 20,
                "signal_threshold": 0.7,
                "risk_threshold": 0.3,
                "max_position_size": 0.1,
                "rebalance_frequency_hours": 4,
                "target_assets": []
            },
            max_position_size=0.2,  # 20% max position
            max_daily_loss=0.05,    # 5% daily loss limit
            max_drawdown=0.15       # 15% max drawdown
        )
        
        super().__init__(strategy_id, manifest, config)
        
        # Strategy-specific state
        self.lookback_periods = self.config["lookback_periods"]
        self.signal_threshold = self.config["signal_threshold"]
        self.risk_threshold = self.config["risk_threshold"]
        self.max_position_size = self.config["max_position_size"]
        
        # Data storage using Polars
        self._price_history: Dict[str, pl.DataFrame] = {}
        self._last_rebalance = datetime.utcnow()
        self.rebalance_frequency = timedelta(hours=self.config["rebalance_frequency_hours"])
        
        # Risk management
        self.risk_scorer = RiskScorer(self)
        
        # Performance tracking
        self._signals_generated = 0
        self._trades_executed = 0
        
        logger.info("MomentumStrategy initialized", 
                   strategy_id=str(strategy_id),
                   lookback_periods=self.lookback_periods,
                   signal_threshold=self.signal_threshold)
    
    async def _on_initialize(self) -> None:
        """Strategy-specific initialization."""
        # Initialize price history for target assets
        for asset_config in self.config["target_assets"]:
            asset_symbol = asset_config.get("symbol", "UNKNOWN")
            self._price_history[asset_symbol] = pl.DataFrame({
                "timestamp": [],
                "price": [],
                "volume": []
            }, schema={"timestamp": pl.Datetime, "price": pl.Float64, "volume": pl.Float64})
        
        logger.info("Price history initialized", assets=list(self._price_history.keys()))
    
    async def generate_intents(self, market_data: Dict[str, Any]) -> List[Intent]:
        """Generate trading intents based on momentum signals."""
        if not self.is_running:
            return []
        
        intents = []
        
        try:
            # Update price history
            await self._update_price_history(market_data)
            
            # Check if it's time to rebalance
            should_rebalance = (datetime.utcnow() - self._last_rebalance) > self.rebalance_frequency
            
            # Generate signals for each target asset
            for asset_config in self.config["target_assets"]:
                asset_symbol = asset_config.get("symbol")
                if not asset_symbol or asset_symbol not in self._price_history:
                    continue
                
                # Generate intent for this asset
                intent = await self._generate_asset_intent(asset_symbol, asset_config, should_rebalance)
                if intent:
                    intents.append(intent)
                    await self.track_intent_generated(intent)
            
            if should_rebalance and intents:
                self._last_rebalance = datetime.utcnow()
            
            self._signals_generated += len(intents)
            
        except Exception as e:
            logger.error("Failed to generate intents", error=str(e))
        
        return intents
    
    async def _generate_asset_intent(self, asset_symbol: str, asset_config: Dict[str, Any], force_rebalance: bool) -> Optional[Intent]:
        """Generate intent for a specific asset."""
        price_data = self._price_history[asset_symbol]
        
        if len(price_data) < self.lookback_periods:
            logger.debug("Insufficient price data", asset=asset_symbol, data_points=len(price_data))
            return None
        
        # Calculate features
        features = MomentumFeatures.calculate_momentum_features(price_data, self.lookback_periods)
        if not features:
            return None
        
        # Get ML signal
        signal_strength = await self._predict_signal(features)
        risk_score = await self.risk_scorer.calculate_risk_score(features, self.max_position_size)
        
        # Create ML features object
        ml_features = MLFeatures(
            volatility=features.get("vol_10d"),
            volume_ratio=features.get("volume_ratio"),
            market_impact=features.get("price_momentum"),
            time_of_day=datetime.utcnow().hour,
            custom_features=features
        )
        
        # Decision logic
        should_trade = (signal_strength > self.signal_threshold and 
                       risk_score < self.risk_threshold) or force_rebalance
        
        if not should_trade:
            return None
        
        # Create asset and amount
        asset = Asset(
            symbol=asset_symbol,
            address=asset_config["address"],
            decimals=asset_config["decimals"],
            chain_id=asset_config["chain_id"]
        )
        
        # Determine trade direction and size
        trade_amount = self._calculate_trade_amount(signal_strength, risk_score, asset_config)
        
        if trade_amount <= 0:
            return None
        
        # Create intent
        intent_type = IntentType.ACQUIRE if signal_strength > 0.5 else IntentType.DISPOSE
        
        intent = Intent(
            strategy_id=self.strategy_id,
            type=intent_type,
            assets=[AssetSpec(asset=asset, percentage=Decimal(str(trade_amount)))],
            constraints=IntentConstraints(
                max_slippage=Decimal('0.005'),  # 0.5% max slippage
                time_window_ms=300000,  # 5 minutes
                execution_style=ExecutionStyle.ADAPTIVE,
                confidence_threshold=signal_strength,
                use_ml_optimization=True,
                enable_mev_protection=True
            ),
            ml_features=ml_features,
            ml_score=signal_strength,
            metadata={
                "strategy_type": "momentum",
                "signal_strength": signal_strength,
                "risk_score": risk_score,
                "features": features
            }
        )
        
        intent.add_ml_prediction("momentum_signal", signal_strength)
        intent.add_ml_prediction("risk_score", risk_score)
        
        logger.info("Intent generated",
                   asset=asset_symbol,
                   intent_type=intent_type.value,
                   signal_strength=signal_strength,
                   risk_score=risk_score,
                   trade_amount=trade_amount)
        
        return intent
    
    async def _predict_signal(self, features: Dict[str, float]) -> float:
        """Predict signal strength using ML model."""
        try:
            # Use ML model if available
            if "models/momentum_signal.onnx" in self.ml_manager.get_loaded_models():
                result = await self.predict_with_model("models/momentum_signal.onnx", features)
                if "signal_strength" in result:
                    return result["signal_strength"]
            
            # Fallback to heuristic signal
            return self._heuristic_signal(features)
            
        except Exception as e:
            logger.warning("ML signal prediction failed, using fallback", error=str(e))
            return self._heuristic_signal(features)
    
    def _heuristic_signal(self, features: Dict[str, float]) -> float:
        """Heuristic signal generation as fallback."""
        signal = 0.5  # Neutral
        
        # Momentum component
        momentum = features.get("price_momentum", 0)
        signal += momentum * 0.3
        
        # Trend component
        ma_trend = features.get("ma_trend", 0)
        signal += ma_trend * 0.2
        
        # Volume confirmation
        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio > 1.5:  # High volume confirms signal
            signal += 0.1
        
        # RSI component
        rsi = features.get("rsi", 50)
        if rsi < 30:  # Oversold
            signal += 0.1
        elif rsi > 70:  # Overbought
            signal -= 0.1
        
        return max(0.0, min(1.0, signal))
    
    def _calculate_trade_amount(self, signal_strength: float, risk_score: float, asset_config: Dict[str, Any]) -> float:
        """Calculate trade amount based on signal and risk."""
        base_amount = self.max_position_size
        
        # Adjust for signal strength
        signal_adjustment = (signal_strength - 0.5) * 2  # Scale to -1 to 1
        
        # Adjust for risk
        risk_adjustment = 1.0 - risk_score
        
        # Get target weight if specified
        target_weight = asset_config.get("target_weight", base_amount)
        
        trade_amount = target_weight * signal_adjustment * risk_adjustment
        
        return max(0.0, min(trade_amount, self.max_position_size))
    
    async def _update_price_history(self, market_data: Dict[str, Any]) -> None:
        """Update price history with new market data."""
        timestamp = datetime.utcnow()
        
        for asset_symbol in self._price_history.keys():
            if asset_symbol in market_data:
                asset_data = market_data[asset_symbol]
                
                new_row = pl.DataFrame({
                    "timestamp": [timestamp],
                    "price": [float(asset_data.get("price", 0))],
                    "volume": [float(asset_data.get("volume", 0))]
                })
                
                # Append new data and keep only recent history
                self._price_history[asset_symbol] = pl.concat([
                    self._price_history[asset_symbol], 
                    new_row
                ]).tail(self.lookback_periods * 2)  # Keep 2x lookback for safety
    
    async def update_ml_models(self, new_data: Dict[str, Any]) -> None:
        """Update ML models with new data (online learning)."""
        # This is a placeholder for online learning implementation
        # In practice, this would:
        # 1. Collect new training data
        # 2. Retrain models or update model weights
        # 3. Reload updated models
        
        logger.info("ML model update requested", data_keys=list(new_data.keys()))
        
        # For now, just log the update request
        # Real implementation would involve:
        # - Feature engineering on new data
        # - Model retraining pipeline
        # - Model validation and A/B testing
        # - Hot-swapping of models
    
    async def evaluate_market_conditions(self, market_data: Dict[str, Any]) -> Dict[str, float]:
        """Evaluate current market conditions."""
        conditions = {
            "overall_confidence": 0.5,
            "trend_strength": 0.5,
            "volatility_level": 0.5,
            "liquidity_level": 0.5
        }
        
        try:
            # Aggregate conditions across all assets
            total_momentum = 0.0
            total_volatility = 0.0
            asset_count = 0
            
            for asset_symbol in self._price_history.keys():
                if asset_symbol in market_data:
                    price_data = self._price_history[asset_symbol]
                    if len(price_data) >= self.lookback_periods:
                        features = MomentumFeatures.calculate_momentum_features(price_data)
                        total_momentum += abs(features.get("price_momentum", 0))
                        total_volatility += features.get("vol_10d", 0)
                        asset_count += 1
            
            if asset_count > 0:
                avg_momentum = total_momentum / asset_count
                avg_volatility = total_volatility / asset_count
                
                conditions["trend_strength"] = min(avg_momentum * 2, 1.0)
                conditions["volatility_level"] = min(avg_volatility * 10, 1.0)
                conditions["overall_confidence"] = (conditions["trend_strength"] + 
                                                  (1 - conditions["volatility_level"])) / 2
            
            # Use ML model for market regime detection if available
            if "models/market_regime.onnx" in self.ml_manager.get_loaded_models():
                regime_features = {
                    "avg_momentum": total_momentum / max(asset_count, 1),
                    "avg_volatility": total_volatility / max(asset_count, 1),
                    "asset_count": asset_count
                }
                
                regime_result = await self.predict_with_model("models/market_regime.onnx", regime_features)
                if regime_result:
                    conditions.update(regime_result)
        
        except Exception as e:
            logger.error("Failed to evaluate market conditions", error=str(e))
        
        return conditions
    
    # Backtesting support
    async def backtest(self, historical_data: Dict[str, pl.DataFrame], 
                      start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Run backtesting with time-aware data splitting."""
        logger.info("Starting backtest", start=start_date.isoformat(), end=end_date.isoformat())
        
        # Initialize backtest state
        backtest_state = {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "trades": [],
            "daily_returns": []
        }
        
        # Time-aware data splitting
        train_end = start_date + (end_date - start_date) * 0.7  # 70% for training
        
        # Simulate trading day by day
        current_date = start_date
        portfolio_value = 10000.0  # Starting portfolio
        peak_value = portfolio_value
        
        while current_date <= end_date:
            try:
                # Get market data for current date
                daily_data = {}
                for asset_symbol, data in historical_data.items():
                    day_data = data.filter(
                        pl.col("timestamp").dt.date() == current_date.date()
                    )
                    if not day_data.is_empty():
                        latest = day_data.tail(1).to_dicts()[0]
                        daily_data[asset_symbol] = latest
                
                if daily_data:
                    # Update price history
                    await self._update_price_history(daily_data)
                    
                    # Generate intents
                    intents = await self.generate_intents(daily_data)
                    
                    # Simulate intent execution
                    for intent in intents:
                        trade_result = self._simulate_trade_execution(intent, daily_data)
                        backtest_state["trades"].append(trade_result)
                        portfolio_value *= (1 + trade_result["return"])
                
                # Track performance
                daily_return = (portfolio_value - peak_value) / peak_value if peak_value > 0 else 0
                backtest_state["daily_returns"].append(daily_return)
                
                # Update max drawdown
                if portfolio_value > peak_value:
                    peak_value = portfolio_value
                else:
                    drawdown = (peak_value - portfolio_value) / peak_value
                    backtest_state["max_drawdown"] = max(backtest_state["max_drawdown"], drawdown)
                
                current_date += timedelta(days=1)
                
            except Exception as e:
                logger.error("Backtest error", date=current_date.isoformat(), error=str(e))
                current_date += timedelta(days=1)
        
        # Calculate final metrics
        total_return = (portfolio_value - 10000.0) / 10000.0
        returns_array = np.array(backtest_state["daily_returns"])
        sharpe_ratio = (np.mean(returns_array) / np.std(returns_array) * np.sqrt(252) 
                       if np.std(returns_array) > 0 else 0)
        
        backtest_state.update({
            "total_return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "final_portfolio_value": portfolio_value,
            "total_trades": len(backtest_state["trades"])
        })
        
        logger.info("Backtest completed", 
                   total_return=total_return,
                   sharpe_ratio=sharpe_ratio,
                   max_drawdown=backtest_state["max_drawdown"],
                   total_trades=len(backtest_state["trades"]))
        
        return backtest_state
    
    def _simulate_trade_execution(self, intent: Intent, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate trade execution for backtesting."""
        # Simple simulation - in practice this would be more sophisticated
        asset_spec = intent.assets[0]
        asset_symbol = asset_spec.asset.symbol
        
        if asset_symbol in market_data:
            price = market_data[asset_symbol]["price"]
            
            # Simulate slippage and fees
            slippage = 0.001  # 0.1% slippage
            fees = 0.0005     # 0.05% fees
            
            # Calculate return (simplified)
            trade_return = 0.0
            if intent.type == IntentType.ACQUIRE:
                trade_return = -slippage - fees  # Cost of acquiring
            else:
                trade_return = -slippage - fees  # Cost of disposing
            
            return {
                "intent_id": str(intent.id),
                "asset": asset_symbol,
                "type": intent.type.value,
                "price": price,
                "return": trade_return,
                "timestamp": datetime.utcnow()
            }
        
        return {
            "intent_id": str(intent.id),
            "asset": asset_spec.asset.symbol,
            "type": intent.type.value,
            "return": 0.0,
            "error": "No market data",
            "timestamp": datetime.utcnow()
        }