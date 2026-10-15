import assert from 'node:assert/strict'
import test from 'node:test'

import {
	isGroupRole,
	isStaffSession,
	roleLabel,
	screenIdFromHash,
} from './format.js'

test('an empty hash opens the dashboard', () => {
	assert.equal(screenIdFromHash(''), 'dashboard')
	assert.equal(screenIdFromHash('#'), 'dashboard')
	assert.equal(screenIdFromHash(null), 'dashboard')
})

test('a desk hash keeps its screen id', () => {
	assert.equal(screenIdFromHash('#reports'), 'reports')
	assert.equal(screenIdFromHash('#requests'), 'requests')
	assert.equal(screenIdFromHash('#maintenance'), 'maintenance')
	assert.equal(screenIdFromHash('#keys'), 'keys')
	assert.equal(screenIdFromHash('#occupancy'), 'occupancy')
})

test('an unknown hash stays unknown for the desk to reject', () => {
	assert.equal(screenIdFromHash('#not-a-screen'), 'not-a-screen')
})

test('the header role follows the signed-in roles', () => {
	assert.equal(roleLabel('Administrator', []), 'System Manager')
	assert.equal(roleLabel('admin@hotlync.local', ['Accommodation Admin']), 'Accommodation Admin')
	assert.equal(
		roleLabel('manager@hotlync.local', ['Accommodation Manager']),
		'Accommodation Manager',
	)
	assert.equal(roleLabel('staff@hotlync.local', ['Staff']), 'Staff')
	assert.equal(roleLabel('person@hotlync.local', []), 'Signed in')
	assert.equal(
		roleLabel('person@hotlync.local', ['Staff', 'Accommodation Admin']),
		'Accommodation Admin',
	)
})

test('only a staff login without a desk role uses the staff home', () => {
	assert.equal(isStaffSession({ roles: ['Staff'] }), true)
	assert.equal(isStaffSession({ roles: ['Staff', 'Accommodation Manager'] }), false)
	assert.equal(isStaffSession({ roles: ['Accommodation Admin'] }), false)
	assert.equal(isStaffSession(null), false)
})

test('group roles are the logins that can manage access', () => {
	assert.equal(isGroupRole(['System Manager']), true)
	assert.equal(isGroupRole(['Accommodation Admin']), true)
	assert.equal(isGroupRole(['Accommodation Manager']), false)
	assert.equal(isGroupRole(['Staff']), false)
	assert.equal(isGroupRole(null), false)
})
