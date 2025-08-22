"""
Intent validation logc.

This module provides validation for intent constraints and business rules.
"""

import structlog
from typing import List, Tuple, Optional
from decimal import Decimal

import asyncpg

from ...types import Intent, Asset, AssetAmount, Venue, Chain

logger = structlog.get_logger()


class IntentValidator:
    """Validates intents against various constraints and rules."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        # In a real system, this would be periodically updated
        self.supported_venues_by_chain: Dict[int, List[Venue]] = {
            Chain.ETHEREUM.value: [Venue.UNISWAP_V3, Venue.CURVE, Venue.BALANCER],
            Chain.ARBITRUM.value: [Venue.UNISWAP_V3, Venue.SUSHISWAP],
            Chain.BASE.value: [Venue.UNISWAP_V3]
        }
    
    async def validate(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Run all validation checks and return errors and warnings."""
        errors: List[str] = []
        warnings: List[str] = []
        
        # Run all validation methods
        validation_checks = [
            self._validate_basic_constraints,
            self._validate_asset_specifications,
            self._validate_venue_constraints,
            self._validate_gas_costs,
            self._validate_against_portfolio # This one is async
        ]
        
        for check in validation_checks:
            if asyncio.iscoroutinefunction(check):
                errs, warns = await check(intent)
            else:
                errs, warns = check(intent)
            errors.extend(errs)
            warnings.extend(warns)
            
        if not errors:
            logger.info("Intent validation successful", intent_id=str(intent.id), warnings=warnings)
        
        return errors, warnings

    def _validate_basic_constraints(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Validate basic intent constraints."""
        errors: List[str] = []
        warnings: List[str] = []
        
        if intent.is_expired:
            errors.append("Intent has already expired")
        
        if intent.constraints.max_slippage > Decimal('0.1'):
            warnings.append("Max slippage is very high (>10%)")
        
        return errors, warnings

    def _validate_asset_specifications(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Validate that asset specifications are consistent."""
        errors: List[str] = []
        warnings: List[str] = []
        
        chain_ids = {spec.asset.chain_id for spec in intent.assets}
        if len(chain_ids) > 1:
            errors.append(f"Multi-chain intents are not yet supported. Found chains: {chain_ids}")
        
        return errors, warnings

    def _validate_venue_constraints(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Validate venue constraints."""
        errors: List[str] = []
        warnings: List[str] = []
        
        chain_id = intent.primary_asset.chain_id
        supported_venues = self.supported_venues_by_chain.get(chain_id, [])
        
        if intent.constraints.allowed_venues:
            for venue in intent.constraints.allowed_venues:
                if venue not in supported_venues:
                    warnings.append(f"Venue {venue.value} is not supported on chain {chain_id}")
        
        return errors, warnings

    def _validate_gas_costs(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Validate gas cost constraints against current estimates."""
        # This would require a gas oracle
        # Placeholder implementation
        return [], []

    async def _validate_against_portfolio(self, intent: Intent) -> Tuple[List[str], List[str]]:
        """Validate intent against current portfolio state."""
        # This would require querying the portfolio read model
        # Placeholder implementation
        return [], []