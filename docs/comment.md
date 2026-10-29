## Fang mutation report

**61.9%** mutation score · 39 killed · 24 survived

Suite: 10 tests, 0.33s baseline. Scope: all.

<details><summary>Surviving mutants (24)</summary>

- `shop/cart.py:17` **Cart.add** · `<=` → `<`  
  Add a test at the boundary where this comparison flips.
- `shop/cart.py:18` **Cart.add** · `"quantity must be positive"` → `""`  
  Assert against a different value so this constant is observable.
- `shop/cart.py:19` **Cart.add** · `"sku"` → `""`  
  Assert against a different value so this constant is observable.
- `shop/cart.py:23` **Cart.subtotal** · `2` → `3`  
  Assert against a different value so this constant is observable.
- `shop/cart.py:30` **Cart.total** · `2` → `3`  
  Assert against a different value so this constant is observable.
- `shop/inventory.py:13` **Inventory.add** · `<` → `<=`  
  Add a test at the boundary where this comparison flips.
- `shop/inventory.py:13` **Inventory.add** · `0` → `1`  
  Assert against a different value so this constant is observable.
- `shop/inventory.py:14` **Inventory.add** · `"cannot add a negative count"` → `""`  
  Assert against a different value so this constant is observable.
- `shop/inventory.py:18` **Inventory.take** · `0` → `1`  
  Assert against a different value so this constant is observable.
- `shop/inventory.py:19` **Inventory.take** · `>` → `>=`  
  Add a test at the boundary where this comparison flips.
- `shop/inventory.py:22` **Inventory.take** · `return True` → `return None`  
  Assert the return value; calling the function is not enough.
- `shop/inventory.py:22` **Inventory.take** · `True` → `False`  
  Assert against a different value so this constant is observable.
- `shop/inventory.py:25` **Inventory.available** · `0` → `1`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:5` **module** · `100.0` → `101.0`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:6` **module** · `9.99` → `10.99`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:10` **module** · `"basic"` → `""`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:12` **module** · `"gold"` → `""`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:12` **module** · `0.10` → `1.1`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:18` **discount_rate** · `0.0` → `1.0`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:23` **discount_for** · `>=` → `>`  
  Add a test at the boundary where this comparison flips.
- `shop/pricing.py:24` **discount_for** · `2` → `3`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:25` **discount_for** · `2` → `3`  
  Assert against a different value so this constant is observable.
- `shop/pricing.py:31` **shipping_fee** · `return EXPRESS_FEE` → `return None`  
  Assert the return value; calling the function is not enough.
- `shop/pricing.py:32` **shipping_fee** · `>=` → `>`  
  Add a test at the boundary where this comparison flips.

</details>
