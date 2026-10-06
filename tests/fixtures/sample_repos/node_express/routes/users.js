const express = require('express');
const router = express.Router();
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');

function requireRole(role) {
  return (req, res, next) => {
    if (req.user && req.user.role === role) return next();
    return res.status(403).json({ error: 'forbidden' });
  };
}

router.get('/users', (req, res) => res.json([]));

router.delete('/users/:id', requireRole('admin'), (req, res) => {
  res.json({ deleted: true });
});

router.post('/login', (req, res) => {
  const token = jwt.sign({ sub: req.body.userId }, 'secret');
  const hashed = bcrypt.hashSync(req.body.password, 10);
  res.json({ token, hashed });
});

module.exports = router;
